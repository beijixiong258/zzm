package cn.aicademiya.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import cn.aicademiya.entity.LearningRecord;

public interface LearningRecordMapper extends BaseMapper<LearningRecord> {
    @org.apache.ibatis.annotations.Select("SELECT * FROM learning_record WHERE id = #{id} FOR UPDATE")
    LearningRecord lockById(@org.apache.ibatis.annotations.Param("id") String id);
}
